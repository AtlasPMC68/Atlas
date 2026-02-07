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
        transformOrigin: 'center center',
      }"
      ref="transformWrapper"
    >
      <img
        v-if="imageUrl"
        ref="imageEl"
        :src="imageUrl"
        class="w-full h-full object-contain select-none pointer-events-none"
        @load="updateSize"
      />
      <svg
        v-if="(points.length > 0 || props.point) && imageEl"
        class="absolute pointer-events-none"
        :style="svgStyle"
        :viewBox="`0 0 ${imageNaturalWidth} ${imageNaturalHeight}`"
        preserveAspectRatio="none"
      >
        <polyline
          v-if="points.length > 0"
          :points="svgPoints"
          fill="none"
          stroke="#dc2626"
          stroke-width="2"
        />
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
  modelValue: {
    type: Array,
    default: () => [], // [ [x,y], ... ] in image pixel space
  },
  point: {
    type: Array,
    default: null, // [x, y] or null
  },
  drawingMode: {
    type: String,
    default: "polyline", // 'polyline' or 'point'
  },
  imageUrl: {
    type: String,
    required: true,
  },
});

const emit = defineEmits(["update:modelValue", "update:point"]);

const container = ref(null);
const imageEl = ref(null);
const width = ref(800);
const height = ref(600);
let isDrawing = false;

const imageNaturalWidth = ref(0);
const imageNaturalHeight = ref(0);

const scale = ref(1);
const offset = ref({ x: 0, y: 0 });
const isPanning = ref(false);
const lastMouse = ref({ x: 0, y: 0 });

// 'click' = place points / draw, 'move' = pan by dragging
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

const points = computed(() => props.modelValue || []);

const svgPoints = computed(() =>
  points.value.map(([x, y]) => `${x},${y}`).join(" "),
);

onMounted(() => {
  updateSize();
});

watch(
  () => props.imageUrl,
  () => {
    // reset when image changes
    emit("update:modelValue", []);
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
  scale.value = Math.min(5, Math.max(0.2, next));
}

function onMouseDown(event) {
  if (!container.value) return;

  // In move mode, start panning instead of drawing
  if (interactionMode.value === 'move') {
    isPanning.value = true;
    lastMouse.value = { x: event.clientX, y: event.clientY };
    return;
  }
  
  if (props.drawingMode === "point") {
    // Point mode: single click to place a point
    setPointFromEvent(event);
  } else {
    // Polyline mode: hold and drag to draw
    isDrawing = true;
    addPointFromEvent(event);
  }
}

function onMouseMove(event) {
  if (!container.value) return;

  // Handle panning independently of drawing
  if (isPanning.value) {
    const dx = event.clientX - lastMouse.value.x;
    const dy = event.clientY - lastMouse.value.y;
    offset.value = { x: offset.value.x + dx, y: offset.value.y + dy };
    lastMouse.value = { x: event.clientX, y: event.clientY };
    return;
  }

  if (!isDrawing) return;
  if (props.drawingMode === "polyline") {
    addPointFromEvent(event);
  }
}

function onMouseUp() {
  isDrawing = false;
  isPanning.value = false;
}

function setPointFromEvent(event) {
  if (!container.value || !imageEl.value) return;

  const containerRect = container.value.getBoundingClientRect();
  const imgRect = imageEl.value.getBoundingClientRect();

  const cx = event.clientX - containerRect.left;
  const cy = event.clientY - containerRect.top;

  const imgLeft = imgRect.left - containerRect.left;
  const imgTop = imgRect.top - containerRect.top;

  const ix = cx - imgLeft;
  const iy = cy - imgTop;

  if (ix < 0 || iy < 0 || ix > imgRect.width || iy > imgRect.height) return;

  const scaleX = imageEl.value.naturalWidth / imgRect.width;
  const scaleY = imageEl.value.naturalHeight / imgRect.height;

  const xPx = ix * scaleX;
  const yPx = iy * scaleY;

  emit("update:point", [xPx, yPx]);
}

function addPointFromEvent(event) {
  if (!container.value || !imageEl.value) return;

  const containerRect = container.value.getBoundingClientRect();
  const imgRect = imageEl.value.getBoundingClientRect();

  // Mouse position in viewport -> container local
  const cx = event.clientX - containerRect.left;
  const cy = event.clientY - containerRect.top;

  // Image top-left inside container (because object-contain + centering)
  const imgLeft = imgRect.left - containerRect.left;
  const imgTop = imgRect.top - containerRect.top;

  // Mouse position relative to displayed image
  const ix = cx - imgLeft;
  const iy = cy - imgTop;

  // Ignore clicks outside the actual image area
  if (ix < 0 || iy < 0 || ix > imgRect.width || iy > imgRect.height) return;

  // Scale displayed coords -> natural pixel coords
  const scaleX = imageEl.value.naturalWidth / imgRect.width;
  const scaleY = imageEl.value.naturalHeight / imgRect.height;

  const xPx = ix * scaleX;
  const yPx = iy * scaleY;


  const next = [...points.value, [xPx, yPx]];
  emit("update:modelValue", next);
}
</script>
