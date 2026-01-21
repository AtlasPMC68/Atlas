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
    />

    <svg
      v-if="points.length > 0"
      class="absolute inset-0 pointer-events-none"
      :viewBox="`0 0 ${width} ${height}`"
      preserveAspectRatio="xMidYMid meet"
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
  const rect = container.value.getBoundingClientRect();
  width.value = rect.width || 800;
  height.value = rect.height || 600;
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
  const rect = container.value.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;

  const next = [...points.value, [x, y]];
  emit("update:modelValue", next);
}
</script>
