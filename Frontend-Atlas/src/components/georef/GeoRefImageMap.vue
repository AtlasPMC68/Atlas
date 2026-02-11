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
        v-if="props.point && imageEl"
        class="absolute pointer-events-none"
        :style="svgStyle"
        :viewBox="`0 0 ${imageNaturalWidth} ${imageNaturalHeight}`"
        preserveAspectRatio="none"
      >
        <circle
          v-if="props.point"
          :cx="props.point[0]"
          :cy="props.point[1]"
          r="6"
          fill="#dc2626"
          stroke="#dc2626"
          stroke-width="2"
          opacity="0.8"
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
});

const emit = defineEmits(["update:point"]);

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
  if (!container.value || !imageEl.value) return {};
  const c = container.value.getBoundingClientRect();
  const i = imageEl.value.getBoundingClientRect();
  return {
    left: `${i.left - c.left}px`,
    top: `${i.top - c.top}px`,
    width: `${i.width}px`,
    height: `${i.height}px`,
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

</script>
