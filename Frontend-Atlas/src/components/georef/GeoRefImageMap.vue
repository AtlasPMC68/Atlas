<template>
  <div
    ref="container"
    class="relative w-full h-full bg-base-200 overflow-hidden cursor-crosshair"
    @mousedown="onMouseDown"
    @mousemove="onMouseMove"
    @mouseup="onMouseUp"
    @mouseleave="onMouseUp"
  >
    <img
      v-if="imageUrl"
      :src="imageUrl"
      ref="imageEl"
      class="w-full h-full object-contain select-none pointer-events-none"
      alt="Carte importée"
      @load="updateSize"
    />

    <svg
      v-if="points.length > 0 && imageEl"
      class="absolute pointer-events-none"
      :style="svgStyle"
      :viewBox="`0 0 ${imageNaturalWidth} ${imageNaturalHeight}`"
      preserveAspectRatio="none"
    >
      <polyline
        :points="svgPoints"
        fill="none"
        stroke="#dc2626"
        stroke-width="2"
      />
    </svg>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [], // [ [x,y], ... ] in image pixel space
  },
  imageUrl: {
    type: String,
    required: true,
  },
});

const emit = defineEmits(["update:modelValue"]);

const container = ref(null);
const imageEl = ref(null);
const width = ref(800);
const height = ref(600);
let isDrawing = false;

const imageNaturalWidth = ref(0);
const imageNaturalHeight = ref(0);
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

function onMouseDown(event) {
  if (!container.value) return;
  isDrawing = true;
  addPointFromEvent(event);
}

function onMouseMove(event) {
  if (!isDrawing || !container.value) return;
  addPointFromEvent(event);
}

function onMouseUp() {
  isDrawing = false;
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
