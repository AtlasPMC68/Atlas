<template>
  <div class="timeline-container">
    <!-- Slider (barre) -->
    <input
      type="range"
      :min="min"
      :max="max"
      v-model.number="internalYear"
      @input="onSliderInput"
      class="slider"
    />

    <!-- Input texte -->
    <input
      type="number"
      min="0"
      max="9999"
      v-model="inputValue"
      @change="onInputChange"
      class="year-input"
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

// Met à jour input si le parent change
watch(
  () => props.year,
  (val) => {
    if (val !== internalYear.value) {
      internalYear.value = val;
      inputValue.value = String(val);
    }
  }
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
  position: fixed;
  bottom: 0;
  left: 0;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 2rem;
  padding-left: 2rem; /* Décalage à gauche */
  background: white; /* Optionnel : fond blanc pour bien voir */
  box-sizing: border-box; /* Pour que padding ne déborde pas */
  height: 4rem; /* Ajuste la hauteur pour contenir le slider et l'input */
  border-top: 1px solid #ddd; /* Optionnel : une bordure en haut */
  z-index: 1000; /* Pour que ça soit au-dessus des autres éléments */
}

.slider {
  flex: 1;
  height: 4px;
  background: #ccc;
  border-radius: 2px;
  appearance: none;
}

.slider::-webkit-slider-thumb {
  appearance: none;
  width: 16px;
  height: 16px;
  background: #2c7be5;
  border-radius: 50%;
  cursor: pointer;
  border: none;
  box-shadow: 0 0 2px rgba(0, 0, 0, 0.4);
}

.year-input {
  width: 80px;
  padding: 4px;
  font-size: 14px;
}
</style>
