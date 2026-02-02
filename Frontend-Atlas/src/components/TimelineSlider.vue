<template>
  <div class="timeline-container">
    <!-- Slider (barre) -->
    <input
      type="range"
      :min="min"
      :max="max"
      v-model.number="internalYear"
      @input="onSliderInput"
      class="range range-primary range-sm flex-1 [--range-fill:0]"
    />

    <!-- Input texte -->
    <input
      type="number"
      min="0"
      max="2025"
      v-model="inputValue"
      @change="onInputChange"
      class="input input-bordered input-sm w-20"
    />
  </div>
</template>

<script setup>
import { ref, watch } from "vue";

const props = defineProps({
  year: Number,
  min: {
    type: Number,
    default: 1400,
  },
  max: {
    type: Number,
    default: () => new Date().getFullYear(),
  },
});

const emit = defineEmits(["update:year"]);
const internalYear = ref(props.year || props.min);
const inputValue = ref(String(internalYear.value));

watch(
  () => props.year,
  (val) => {
    if (val !== internalYear.value) {
      internalYear.value = val;
      inputValue.value = String(val);
    }
  },
);

function onSliderInput() {
  inputValue.value = String(internalYear.value);
  emit("update:year", internalYear.value);
}

function onInputChange() {
  const raw = parseInt(inputValue.value);
  const clamped = Math.min(Math.max(raw || props.min, props.min), props.max);
  internalYear.value = clamped;
  inputValue.value = String(clamped);
  emit("update:year", clamped);
}
</script>

<style scoped>
.timeline-container {
  display: flex;
  align-items: center;
  gap: 2rem;
  padding: 1rem 2rem;
  background: white;
  height: 4rem;
  width: 100%;
  box-sizing: border-box;
  border-top: 1px solid #ddd;
}
</style>
