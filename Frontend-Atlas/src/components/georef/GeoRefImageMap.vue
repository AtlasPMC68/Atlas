<template>
  <div
    ref="container"
    class="relative w-full h-full bg-base-200 overflow-hidden"
    @mousedown="onMouseDown"
    @mousemove="onMouseMove"
    @mouseup="onMouseUp"
    @mouseleave="onMouseUp"
    @wheel.prevent="onWheel"
  >
    <!-- Mode toggle: Click (place points) vs Move (pan) -->
    <div class="absolute top-2 right-2 z-10 flex gap-2">
      <button
        type="button"
        class="btn btn-xs"
        :class="interactionMode === 'click' ? 'btn-primary' : 'btn-ghost'"
        @mousedown.stop
        @click.stop="interactionMode = 'click'"
      >
        Click
      </button>
      <button
        type="button"
        class="btn btn-xs"
        :class="interactionMode === 'move' ? 'btn-primary' : 'btn-ghost'"
        @mousedown.stop
        @click.stop="interactionMode = 'move'"
      >
        Move
      </button>
    </div>

    <div
      class="absolute inset-0"
      :style="{
        transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
        transformOrigin: 'top left',
      }"
    >
      <img
        v-if="imageUrl"
        ref="imageEl"
        :src="imageUrl"
        class="w-full h-full object-contain select-none pointer-events-none"
        @load="updateSize"
      />
      <svg
        v-if="imageEl && matchedPoints.length"
        class="absolute"
        :style="svgStyle"
        :viewBox="`0 0 ${imageNaturalWidth} ${imageNaturalHeight}`"
        preserveAspectRatio="none"
      >
        <!-- Matched world/image pairs as triangles with stable colors -->
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

<script setup>
import { ref, computed, onMounted, watch } from "vue";

const props = defineProps({
  point: {
    type: Array,
    default: null, // [x, y] or null
  },
  imageUrl: {
    type: String,
    required: true,
  },
  // Matched control points passed from parent (for SIFT modal)
  // [{ index, x, y, color }]
  matchedPoints: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["update:point", "select-match"]);

const container = ref(null);
const imageEl = ref(null);

const imageNaturalWidth = ref(0);
const imageNaturalHeight = ref(0);

const scale = ref(1);
const offset = ref({ x: 0, y: 0 });
const isPanning = ref(false);
const lastMouse = ref({ x: 0, y: 0 });

// 'click' = place point, 'move' = pan by dragging
const interactionMode = ref('click');

const svgStyle = computed(() => {
  if (
    !container.value ||
    !imageEl.value ||
    !imageNaturalWidth.value ||
    !imageNaturalHeight.value
  ) {
    return {};
  }

  const c = container.value.getBoundingClientRect();
  const cw = c.width;
  const ch = c.height;

  const natW = imageNaturalWidth.value;
  const natH = imageNaturalHeight.value;

  // Use the same fitting logic as in setPointFromEvent so that
  // the SVG overlay matches exactly the displayed image area
  // (object-contain with possible gray bars around).
  const baseScale = Math.min(cw / natW, ch / natH);
  const displayW = natW * baseScale;
  const displayH = natH * baseScale;
  const offsetX = (cw - displayW) / 2;
  const offsetY = (ch - displayH) / 2;

  return {
    left: `${offsetX}px`,
    top: `${offsetY}px`,
    width: `${displayW}px`,
    height: `${displayH}px`,
  };
});

onMounted(() => {
  updateSize();
});

watch(
  () => props.imageUrl,
  () => {
    updateSize();
  },
);

function updateSize() {
  if (!container.value) return;
  if (imageEl.value) {
    imageNaturalWidth.value = imageEl.value.naturalWidth || 0;
    imageNaturalHeight.value = imageEl.value.naturalHeight || 0;
    console.log(
      "Image natural size:",
      imageNaturalWidth.value,
      imageNaturalHeight.value,
    );
  }
}

function onWheel(e) {
  const factor = 0.001;
  const next = scale.value * (1 - e.deltaY * factor);
  scale.value = Math.min(5, Math.max(1, next));

  // After zooming, make sure the content stays within bounds
  clampOffset();
}

function onMouseDown(event) {
  if (!container.value) return;

  // In move mode, start panning instead of drawing
  if (interactionMode.value === 'move') {
    isPanning.value = true;
    lastMouse.value = { x: event.clientX, y: event.clientY };
    return;
  }

  // Click mode: single click to place a point
  setPointFromEvent(event);
}

function onMouseMove(event) {
  if (!container.value) return;

  // Handle panning independently of drawing
  if (isPanning.value) {
    const dx = event.clientX - lastMouse.value.x;
    const dy = event.clientY - lastMouse.value.y;

    // Apply drag
    offset.value = { x: offset.value.x + dx, y: offset.value.y + dy };

    // Clamp so the scaled content (the wrapper that matches
    // the container size) always covers the container.
    // At scale = 1 this prevents any panning (you already see
    // the whole image with gray bars). For scale > 1 you can
    // pan, but never beyond the container edges.
    clampOffset();

    lastMouse.value = { x: event.clientX, y: event.clientY };
    return;
  }
}

function onMouseUp() {
  isPanning.value = false;
}

function clampOffset() {
  if (!container.value) return;

  const rect = container.value.getBoundingClientRect();
  const cw = rect.width;
  const ch = rect.height;

  const s = scale.value;

  // The transformed wrapper has size (cw * s, ch * s) and we
  // want it to always fully cover the container (0..cw, 0..ch).
  // This gives classic bounds for panning a zoomed element that
  // is originally the same size as the viewport.
  const minX = cw - cw * s;
  const maxX = 0;
  const minY = ch - ch * s;
  const maxY = 0;

  offset.value = {
    x: Math.min(maxX, Math.max(minX, offset.value.x)),
    y: Math.min(maxY, Math.max(minY, offset.value.y)),
  };
}

function onTriangleClick(index) {
  // Notify parent that an existing matched point was selected
  emit("select-match", index);
}

function trianglePoints(m) {
  // Build an upright triangle centered on the image point.
  // Size is kept roughly constant on screen by dividing by scale.
  const s = scale.value || 1;
  const size = 36 / s;
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

function setPointFromEvent(event) {
  if (!container.value || !imageEl.value) return;

  const natW = imageEl.value.naturalWidth;
  const natH = imageEl.value.naturalHeight;
  if (!natW || !natH) return;

  const containerRect = container.value.getBoundingClientRect();
  const cw = containerRect.width;
  const ch = containerRect.height;

  // Mouse position in viewport -> container local
  const cx = event.clientX - containerRect.left;
  const cy = event.clientY - containerRect.top;

  // Undo current pan/zoom applied to the wrapper
  const localX = (cx - offset.value.x) / scale.value;
  const localY = (cy - offset.value.y) / scale.value;

  // How the image is fitted inside the container with object-contain
  const baseScale = Math.min(cw / natW, ch / natH);
  const displayW = natW * baseScale;
  const displayH = natH * baseScale;
  const offsetX = (cw - displayW) / 2;
  const offsetY = (ch - displayH) / 2;

  // Coords inside the displayed image content
  const ix = localX - offsetX;
  const iy = localY - offsetY;

  if (ix < 0 || iy < 0 || ix > displayW || iy > displayH) return;

  // Back to original pixel space
  const xPx = ix / baseScale;
  const yPx = iy / baseScale;

  emit("update:point", [xPx, yPx]);
}

defineExpose({
  // Allow parent to force the component back into click mode
  focusClickMode() {
    interactionMode.value = 'click';
  },
});

</script>
